// SPDX-License-Identifier: Apache-2.0
#include "BipedAirRuntime.h"
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
bool BipedAirRuntime::Load(const SettingsDatabase& data,std::string& error)
{BipedAirRuntime next;if(!next.checks.Load(data,error))return false;*this=next;error.clear();return true;}
bool BipedAirRuntime::ConsumeSelector(BipedRuntimeOwners v,std::string& error)
{std::optional<std::size_t> selected;return v.selector.Consume(v.physical.world,BipedRuntimeAirContext(v.processed),v.selector.settings.deck_center_to_truck,selected,error);}
bool BipedAirRuntime::Enter(BipedRuntimeOwners v,BipedGroundRuntime& ground,std::string& error)
{
    state.Reset();v.landing.Reset();const auto entry=EnterInput(v);state.BeginEnterAfterReset(entry);
    EnterBipedAirFeet(v.feet,v.processed,v.ik.state);
    if(!v.life.skeleton_controller.Request(4,v.physical.skeleton_collision,error))return false;
    if(!v.selector.core.sampling.preinitialized_8494)
    {
        OffboardAirLaunchPacket packet;if(!LaunchPacket(v,ground,packet,error))return false;
        if(!v.selector.Launch(v.physical.world,packet,BipedRuntimeGravity(v.physical),BipedRuntimeAirContext(v.processed),error))return false;
    }
    const auto& p=v.processed;Mat4 previous;for(unsigned n=0;n<4;++n){const auto& w=p.effective_anim_transform_192[n];std::memcpy(previous[n].data(),w.data(),16);}
    Vec4 velocity;std::memcpy(velocity.data(),p.vectors_544_560_592_608[3].data(),16);
    ground.controller.Place({entry.animation_frame,velocity,entry.body_position_15872,p.state_2508,p.state_2504,previous});
    state.FinishEnter(EnterInput(v));error.clear();return true;
}
void BipedAirRuntime::Exit(OffboardAirSelector& selector){state.Exit(selector.core.sampling);}
void BipedAirRuntime::Fill(BipedRuntimeOwners v) const
{PublishBipedAirFields(state.Output(),v.publication.off_board);PublishBipedFeet(v.feet,v.publication.off_board);v.landing.Publish(v.publication.off_board,v.publication.collision.vector_48,v.publication.collision.flag_3482);}
}
