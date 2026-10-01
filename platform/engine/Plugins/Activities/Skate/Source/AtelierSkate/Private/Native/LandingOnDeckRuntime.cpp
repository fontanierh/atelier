// SPDX-License-Identifier: Apache-2.0
#include "LandingOnDeckRuntime.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
Vec4 LandingValue(RawVector words){Vec4 v;std::memcpy(v.data(),words.data(),16);return v;}
float LandingWord(std::uint32_t word){float v;std::memcpy(&v,&word,4);return v;}
}
bool LandingOnDeckRuntime::Load(const SettingsDatabase& data,std::string& error)
{
    LandingOnDeckRuntime next;if(!next.configuration.Load(data,error))return false;*this=next;error.clear();return true;
}
void LandingOnDeckRuntime::ClearIk(FootIk& ik)
{
    for(auto& limb:ik.state.limbs){limb.board_blend=0;limb.external_blend=0;limb.mode=foot_ik::Mode::Disabled;}
    ik.state.EnableFeet(false);
}
bool LandingOnDeckRuntime::Enter(LandingOnDeckOwners v,std::string& error)
{
    auto s=v.shared;
    if(!s.life.skeleton_controller.Request(6,s.physical.skeleton_collision,error))return false;
    const auto p=s.processed;if(!s.toolkit){error="Landing entry requires the completed board toolkit";return false;}
    const auto board=s.toolkit->deck;
    const auto hips=ComposeSkeletonAffine(s.physical.roots.animation_to_world,s.physical.animation_record.pose[23]);
    state.Enter(s.landing.manager,{p.category_2516,(p.flags_2480&0x1000)!=0,s.animation_input.extra.jump_strength,board[3],LandingValue(p.vectors_544_560_592_608[2]),LandingValue(p.vectors_544_560_592_608[3]),LandingValue(p.vectors_400_416[0]),LandingValue(p.vectors_544_560_592_608[0]),hips[1],LandingValue(p.effective_anim_transform_192[0]),(p.flags_2476&4)!=0});
    ClearIk(s.ik);
    auto& f=s.physical;LiveBoardPossessionEffects effects(f.board,s.life.board_animated_290,f.board_wiping_out,f.possession_live,f.settings.board.collision,p.timestep_2604);
    effects.DisableAnimation();effects.StandardBoard();f.possession_live.PublishVolumes(f.settings.board.collision);
    if(state.hippy)v.wobble.Trigger(false,(((p.flags_2468>>20)^(p.flags_2476>>2))&1)!=0);
    error.clear();return true;
}
bool LandingOnDeckRuntime::Advance(LandingOnDeckOwners v,std::string& error)
{
    auto s=v.shared;const auto p=s.processed;
    if(!s.toolkit){error="Landing update requires the completed board toolkit";return false;}
    const auto board=s.toolkit->deck;const auto forward=s.toolkit->effective[2];
    auto scene=OffboardStaticScene::Create(s.physical.world,error);if(!scene)return false;
    LandingDeckUpdateOutput output;if(!s.landing.Update(*scene,{s.processed,s.toolkit},output,error))return false;
    state.Align(configuration.state,forward,LandingValue(p.effective_anim_transform_192[2]),p.state_timer_2664,LandingWord(p.vectors_544_560_592_608[3][1]),s.animation_input.extra.physical_body_spin);
    if(!UpdateSkeleton(v,output.position,error))return false;
    state.AdvanceSpin(output);
    const auto& manager=s.landing.manager;
    if(AirTrajectoryVelocityAt(manager.trajectory_32,manager.elapsed_160)[1]<0)
    {
        const float time=LandingOnDeckState::AccurateTime(board[3][1],LandingWord(p.vectors_400_416[0][1]),LandingWord(p.vectors_544_560_592_608[3][1]),{s.physical.skeleton.record.pose[15][3][1],s.physical.skeleton.record.pose[19][3][1]},p.wheel_count_2556);
        state.time_to_land=time;state.near_deck=time<.016000001f;Vec4 offset;
        if(!s.landing.CalculateAccurateIkOffset({s.processed,s.toolkit},s.physical.roots.animation_to_world,s.physical.animation_record.centre_of_mass,s.animated.unadjusted_board[3],time,offset,error))return false;
        if(state.near_deck)v.wobble.Trigger(true,(((p.flags_2468>>20)^(p.flags_2476>>2))&1)!=0);
    }
    if(std::abs(s.animated.unadjusted_board[2][2])>=.97000003f)
    {if((p.flags_2484&2)==0&&state.time_to_land<.2f)s.ik.state.EnableFeet(true);}
    else ClearIk(s.ik);
    state.Finish(configuration.state,LandingWord(p.vectors_544_560_592_608[3][1]));error.clear();return true;
}
bool LandingOnDeckRuntime::PostPhysics(LandingOnDeckOwners v,const WipeoutFrame& frame,std::string& error)
{
    auto s=v.shared;if(!s.landing.PostPhysics({s.processed,s.toolkit},error))return false;
    if(!s.landing.Fill().can_land_316)s.wipeout.state.Request(24,0);
    if(state.dangerous)s.wipeout.state.Request(27,0);
    return s.wipeout.CheckAirCollision(s.processed,frame,error);
}
void LandingOnDeckRuntime::Exit(LandingOnDeckOwners v){v.shared.landing.Reset();}
}
