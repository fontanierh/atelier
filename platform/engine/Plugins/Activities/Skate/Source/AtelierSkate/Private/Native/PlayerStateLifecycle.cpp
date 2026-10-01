// SPDX-License-Identifier: Apache-2.0
#include "PlayerStateLifecycle.h"
namespace atelier::skate
{
namespace
{
void StopController(SkateboardControllerFields& c,SkateboardControllerActions& a)
{
    if (!c.system_on_452) return;
    const auto prior=c.state_448;c.word_444=0;
    if (prior!=0) {a.LetGoOfSkateboard();c.state_448=0;}
    c.system_on_452=false;
}
void PrepareController(PhysicalStateId requested,SkateboardControllerFields& c,std::uint32_t flags,SkateboardControllerActions& a)
{
    if (requested!=PhysicalStateId::BipedGround&&requested!=PhysicalStateId::BipedAir&&requested!=PhysicalStateId::OffBoardPushing) {StopController(c,a);return;}
    if (c.system_on_452) return;
    c.word_444=0;
    if ((flags&(0x80|0x100))!=0) {if (c.state_448!=2) {a.LetGoOfSkateboard();c.state_448=2;}}
    else if (c.state_448!=1) {a.HoldSkateboard();c.state_448=1;}
    c.system_on_452=true;
}
}
bool PhysicalPlayerStateLifecycle::SetPhysicsState(std::uint32_t raw,StateChangeData& d,PhysicalStateCalls& states,SkateboardControllerActions& actions,StateBinding& result,std::uint32_t& unknown)
{
    const auto requested=ParsePhysicalStateId(raw);if (!requested) {unknown=raw;return false;}
    PrepareController(*requested,d.skateboard_controller,d.processed.flags_2480,actions);
    d.player.word_1312=0;d.player.scalar_1344=0.0f;d.processed.scalar_2664=0.0f;d.processed.word_2564=0;
    const auto previous=states.GetType(active_);const auto before=PhysicalStateCategory(previous),after=PhysicalStateCategory(*requested);
    d.processed.previous_state_2504=std::uint32_t(previous);d.processed.previous_category_2516=before;d.processed.requested_state_2500=raw;d.processed.current_state_2508=raw;d.processed.current_category_2512=after;
    if (after!=before) d.player.previous_category_latch_1336=before;
    d.processed.previous_category_latch_2520=d.player.previous_category_latch_1336;
    states.Exit({active_,active_});active_=StateBinding::New(*requested);states.Enter({active_,active_});result=active_;return true;
}
}
