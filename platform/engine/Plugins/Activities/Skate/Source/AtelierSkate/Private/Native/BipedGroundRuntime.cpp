// SPDX-License-Identifier: Apache-2.0
#include "BipedGroundRuntime.h"
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
BipedGroundRuntime::BipedGroundRuntime(OffboardSettings s):controller(std::move(s.controller),s.metrics),
    movement_vs_stick_angle(s.movement_vs_stick_angle),turn_vs_stick_angle(s.turn_vs_stick_angle),air_launch(s.air_launch),grab_settings(s.board){}
std::optional<BipedGroundRuntime> BipedGroundRuntime::Load(const SettingsDatabase& data,const AnimationMetadata& metadata,std::string& error)
{
    OffboardSettings s;if(!s.Load(data,metadata,error))return std::nullopt;BipedGroundRuntime next(std::move(s));
    if(!next.skeleton_state.Load(data,error)||!next.geometry.Load(data,error)||!next.collision_settings.Load(data,error))return std::nullopt;
    error.clear();return next;
}
void BipedGroundRuntime::Reset(OffboardContactToolkit& toolkit)
{
    result.reset();state.flags_144_to_150={};state.counter_152=0;state.counter_156=0;state.elapsed_160=0;toolkit.ResetHistory();
    state=BipedGroundState{};contact=OffboardContactPrefix{};geometry_adjustment.reset();
}
void BipedGroundRuntime::EnterCore(BipedGroundEntryInput input,std::uint32_t current,Mat4 previous,OffboardContactToolkit& toolkit)
{
    Reset(toolkit);geometry.Reset();const auto placement=state.Enter(input);
    controller.Place({placement.frame,placement.planar_velocity,placement.body_position,current,input.previous_state_2504,previous});
}
BipedGroundResult BipedGroundRuntime::Run(const BipedGroundJob& job){const auto next=controller.StepGround(job);result=next;return next;}
void BipedGroundRuntime::Exit(OffboardContactToolkit& toolkit){toolkit.ResetHistory();geometry.Reset();}
}
