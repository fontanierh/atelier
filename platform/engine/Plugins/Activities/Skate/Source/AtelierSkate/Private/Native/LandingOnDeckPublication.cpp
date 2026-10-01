// SPDX-License-Identifier: Apache-2.0
#include "LandingOnDeckRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace{RawVector LandingRaw(Vec4 v){RawVector w;std::memcpy(w.data(),v.data(),16);return w;}}
bool LandingOnDeckRuntime::Fill(LandingOnDeckOwners v,std::string& error) const
{
    if(!state.output){error="Landing Fill requires its completed Update";return false;}
    const auto& output=*state.output;auto& physical=v.shared.publication;auto& off=physical.off_board;
    off.trajectory_valid_331=output.trajectory_valid;off.scalar_152=output.elapsed;off.vector_176=LandingRaw(output.launch_position);off.vector_208=LandingRaw(output.landing_position);
    off.scalar_92=output.landing_time;off.vector_192=LandingRaw(output.normal);off.vector_240=LandingRaw(output.apex_position);off.scalar_156=output.apex_time;off.vector_224=LandingRaw(output.direction);off.vector_160=LandingRaw(output.up);
    off.scalar_32=state.time_to_land;off.flag_315=state.near_deck;off.flag_318=state.turning;
    physical.ground.hippy_takeoff_323=state.takeoff_frames>0;physical.ground.hippy_jumping_322=state.hippy;physical.ground.landing_half_turns_312=state.LandingHalfTurns();
    v.shared.landing.Publish(off,physical.collision.vector_48,physical.collision.flag_3482);error.clear();return true;
}
}
